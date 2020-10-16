// ***************************************************************************
// *                        TemplateLoader                              *
// ***************************************************************************


// check if PypeHarmony is defined and if not, load it.
if (typeof PypeHarmony !== 'undefined') {
  var PYPE_HARMONY_JS = System.getenv('PYPE_HARMONY_JS');
  include(PYPE_HARMONY_JS + '/pype_harmony.js');
}


/**
 * @namespace
 * @classdesc Image Sequence loader JS code.
 */
TemplateLoader = function() {};


/**
 * Load template as container.
 * @function
 * @param {array} args Arguments, see example.
 * @return {string} Name of container.
 *
 * @example
 * // arguments are in following order:
 * var args = [
 *  templatePath, // Path to tpl file.
 *  assetName,    // Asset name.
 *  subsetName,   // Subset name.
 *  groupId       // unique ID (uuid4)
 * ];
 */
TemplateLoader.prototype.loadContainer = function(args) {
  var doc = $.scn;
  var templatePath = args[0];
  var assetName = args[1];
  var subset = args[2];
  var groupId = args[3];

  // Get the current group
  nodeViewWidget = $.app.getWidgetByName('Node View');
  if (!nodeViewWidget) {
    $.alert('You must have a Node View open!', 'No Node View!', 'OK!');
    return;
  }

  nodeViewWidget.setFocus();
  nodeView = view.currentView();
  if (!nodeView) {
    currentGroup = doc.root;
  } else {
    currentGroup = doc.$node(view.group(nodeView));
  }

  // Get a unique iterative name for the container group
  var num = 0;
  var containerGroupName = '';
  do {
    containerGroupName = assetName + '_' + (num++) + '_' + subset;
  } while (currentGroup.getNodeByName(containerGroupName) != null);

  // import the template
  var tplNodes = currentGroup.importTemplate(templatePath);
  MessageLog.trace(tplNodes);
  // Create the container group
  var groupNode = currentGroup.addGroup(
      containerGroupName, false, false, tplNodes);

  // Add uuid to attribute of the container group
  node.createDynamicAttr(groupNode, 'STRING', 'uuid', 'uuid', false);
  node.setTextAttr(groupNode, 'uuid', 1.0, groupId);

  return String(groupNode);
};


/**
 * Replace existing node container.
 * @function
 * @param  {string}  dstNodePath Harmony path to destination Node.
 * @param  {string}  srcNodePath Harmony path to source Node.
 * @param  {string}  renameSrc   ...
 * @param  {boolean} cloneSrc    ...
 * @param  {array}   linkColumns ...
 * @return {boolean}             Success
 * @todo   This is work in progress.
 */
TemplateLoader.prototype.replaceNode = function(
    dstNodePath, srcNodePath, renameSrc, cloneSrc, linkColumns) {
  var doc = $.scn;
  var srcNode = doc.$node(srcNodePath);
  var dstNode = doc.$node(dstNodePath);
  // var dstNodeName = dstNode.name;
  var replacementNode = srcNode;
  // var dstGroup = dstNode.group;
  $.beginUndo();
  if (cloneSrc) {
    var replacementNode = doc.$node(
        Y.nodeTools.copy_paste_node(
            srcNodePath, dstNode.name + '_CLONE', dstNode.group.path));
  } else {
    if (replacement_node.group.path != src_node.group.path) {
      replacement_node.moveToGroup(dst_group);
    }
  }
  var inLinks = dstNode.getInLinks();
  for (l in inLinks) {
    if (Object.prototype.hasOwnProperty.call(inLinks, l)) {
      var link = inLinks[l];
      inPort = Number(link.inPort);
      outPort = Number(link.outPort);
      outNode = link.outNode;
      success = replacement_node.linkInNode(outNode, inPort, outPort);
      if (success) {
        log('Successfully connected ' + outNode + ' : ' +
            outPort + ' -> ' + replacementNode + ' : ' + inPort);
      } else {
        log('Failed to connect ' + outNode + ' : ' +
            outPort + ' -> ' + replacementNode + ' : ' + inPort);
      }
    }
  }

  var outLinks = dstNode.getOutLinks();
  for (l in outLinks) {
    if (Object.prototype.hasOwnProperty.call(outLinks, l)) {
      var link = out_links[l];
      inPort = Number(link.inPort);
      outPort = Number(link.outPort);
      inNode = link.inNode;
      // first we must disconnect the port from the node being
      // replaced to this links inNode port
      inNode.unlinkInPort(inPort);
      success = replacement_node.linkOutNode(in_node, out_port, in_port);
      if (success) {
        log('Successfully connected ' + inNode + ' : ' +
              inPort + ' <- ' + replacementNode + ' : ' + outPort);
      } else {
        if (in_node.type == 'MultiLayerWrite') {
          log('Attempting standard api to connect the nodes...');
          success = node.link(
              replacementNode, outPort, inNode,
              inPort, node.numberOfInputPorts(inNode) + 1);
          if (success) {
            log('Successfully connected ' + inNode + ' : ' +
                inPort + ' <- ' + replacementNode + ' : ' + outPort);
          }
        }
      }
      if (!success) {
        log('Failed to connect ' + inNode + ' : ' +
            inPort + ' <- ' + replacementNode + ' : ' + outPort);
        return false;
      }
    }
  }
};


TemplateLoader.prototype.askForColumnsUpdate = function() {
  // Ask user if they want to also update columns and
  // linked attributes here
  return ($.confirm(
      'Would you like to update in place and reconnect all \n' +
      'ins/outs, attributes, and columns?',
      'Update & Replace?\n' +
      'If you choose No, the version will only be loaded.',
      'Yes',
      'No'));
};

// add self to Pype Loaders
PypeHarmony.Loaders.TemplateLoader = new TemplateLoader();
